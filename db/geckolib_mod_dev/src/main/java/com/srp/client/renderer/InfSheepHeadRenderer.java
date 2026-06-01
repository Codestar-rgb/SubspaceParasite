package com.srp.client.renderer;

import com.srp.client.model.InfSheepHeadModel;
import com.srp.entity.InfSheepHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfSheepHeadRenderer extends GeoEntityRenderer<InfSheepHeadEntity> {

    public InfSheepHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfSheepHeadModel());
    }
}
